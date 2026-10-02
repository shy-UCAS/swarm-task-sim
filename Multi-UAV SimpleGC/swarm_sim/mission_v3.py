"""TaskSpec v3: scene/intent/planner separation with an explicit WP-E boundary."""

import copy

from .families import FAMILY_SCHEME, scene_family_id
from .mission_schema import _bounds, _enum, _identifier, _numeric, _object, within_world
from .registry import PlanResult, get_intent, get_planner
from .scenario import number, validate


CONTROL_MODES = ("waypoint_barrier_v1", "semantic_phase_route_v1")


def normalize_v3(spec):
    """Normalize a new deep copy. Legacy normalizers never pass through here."""
    spec = copy.deepcopy(spec)
    _object(spec, "TaskSpec v3", ("schema_version", "task_id", "family_id", "family_scheme", "seed",
                                 "scenario", "mission", "planner", "execution"), optional=("family_id", "family_scheme"))
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 3:
        raise ValueError("TaskSpec schema_version must be integer 3")
    _identifier(spec["task_id"], "task_id")
    if type(spec["seed"]) is not int or not 0 <= spec["seed"] <= 2**63 - 1:
        raise ValueError("seed must be an integer in [0, 2**63 - 1]")
    scenario = _object(spec["scenario"], "scenario", (
        "scene_id", "origin", "world", "regions", "restricted_regions", "vehicles", "platform"))
    _identifier(scenario["scene_id"], "scenario.scene_id")
    origin = _object(scenario["origin"], "origin", ("lat", "lon", "alt_msl_m"))
    for key, low, high in (("lat", -80, 80), ("lon", -179, 179), ("alt_msl_m", -400, 8000)):
        _numeric(origin, key, "origin", low, high)
    world = _object(scenario["world"], "world", ("east_bounds_m", "north_bounds_m", "flight_up_bounds_m"))
    for key in ("east_bounds_m", "north_bounds_m"):
        _bounds(world, key, -2000, 2000)
    _bounds(world, "flight_up_bounds_m", 3, 100)
    if not isinstance(scenario["restricted_regions"], list) or scenario["restricted_regions"]:
        raise ValueError("restricted_regions must be empty; obstacle routing is not supported")
    regions = scenario["regions"]
    if not isinstance(regions, list) or not regions:
        raise ValueError("scenario.regions must contain at least one rectangle")
    region_ids = set()
    for region in regions:
        _object(region, "region", ("id", "type", "min_east_m", "min_north_m", "width_m", "height_m"))
        _identifier(region["id"], "region.id")
        if region["id"] in region_ids:
            raise ValueError("duplicate region ID")
        region_ids.add(region["id"])
        _enum(region, "type", "region", ("rectangle",))
        for key in ("min_east_m", "min_north_m"):
            _numeric(region, key, "region", -2000, 2000)
        for key in ("width_m", "height_m"):
            _numeric(region, key, "region", .01, 4000)
        if not (within_world(region["min_east_m"], region["min_north_m"], world)
                and within_world(region["min_east_m"] + region["width_m"],
                                 region["min_north_m"] + region["height_m"], world)):
            raise ValueError("region extends outside world/backend bounds")
    vehicles = scenario["vehicles"]
    if not isinstance(vehicles, list) or not 1 <= len(vehicles) <= 6:
        raise ValueError("v3 supports 1 to 6 vehicles")
    identities, sysids = set(), set()
    for vehicle in vehicles:
        _object(vehicle, "vehicle", ("id", "sysid", "east_m", "north_m", "heading_deg"), optional=("heading_deg",))
        agent = _identifier(vehicle["id"], "vehicle.id", 48)
        if agent in identities:
            raise ValueError("duplicate vehicle ID")
        identities.add(agent)
        if type(vehicle["sysid"]) is not int or not 1 <= vehicle["sysid"] <= 250:
            raise ValueError("vehicle.sysid must be an integer in [1, 250]")
        if vehicle["sysid"] in sysids:
            raise ValueError("duplicate vehicle sysid")
        sysids.add(vehicle["sysid"])
        for key in ("east_m", "north_m"):
            _numeric(vehicle, key, "vehicle", -2000, 2000)
        vehicle.setdefault("heading_deg", 0.0)
        _numeric(vehicle, "heading_deg", "vehicle", 0, 360)
        if not within_world(vehicle["east_m"], vehicle["north_m"], world):
            raise ValueError(f"vehicle {agent} starts outside world bounds")
    scenario["vehicles"] = sorted(vehicles, key=lambda v: v["id"])
    scenario["regions"] = sorted(regions, key=lambda r: r["id"])
    platform = _object(scenario["platform"], "platform", (
        "id", "max_speed_m_s", "max_climb_rate_m_s", "max_horizontal_accel_m_s2", "max_path_length_m",
        "max_airborne_time_s", "reserve_time_s", "dynamics_validation"))
    _enum(platform, "id", "platform", ("basic_multirotor_nominal_v1",))
    _enum(platform, "dynamics_validation", "platform", ("execution_proxy_only",))
    for key, low, high in (("max_speed_m_s", .5, 100), ("max_climb_rate_m_s", .01, 100),
            ("max_horizontal_accel_m_s2", .01, 1000), ("max_path_length_m", .01, 1000000),
            ("max_airborne_time_s", .01, 1000000), ("reserve_time_s", 0, 1000000)):
        _numeric(platform, key, "platform", low, high)
    if platform["reserve_time_s"] >= platform["max_airborne_time_s"]:
        raise ValueError("reserve_time_s must be less than max_airborne_time_s")

    mission = _object(spec["mission"], "mission", ("intent", "target_region_id", "return_required", "intent_params"))
    intent = get_intent(mission["intent"])
    if not isinstance(mission["target_region_id"], str) or mission["target_region_id"] not in region_ids:
        raise ValueError("mission references an unknown target_region_id")
    if type(mission["return_required"]) is not bool:
        raise ValueError("mission.return_required must be boolean")
    if mission["return_required"] and "return" not in intent.semantic_phases:
        raise ValueError("return_required needs a registered return semantic phase")
    if not isinstance(mission["intent_params"], dict):
        raise ValueError("mission.intent_params must be an object")
    mission["intent_params"] = intent.normalize_params(mission["intent_params"])
    if not isinstance(mission["intent_params"], dict):
        raise ValueError("intent normalizer must return an object")
    if mission["intent_params"].get("objective") not in intent.objectives:
        raise ValueError("intent_params.objective must match the registered intent objectives")
    planner = _object(spec["planner"], "planner", ("name", "params"))
    plugin = get_planner(planner["name"])
    if planner["name"] not in intent.allowed_planners:
        raise ValueError("intent and planner mismatch: planner is not allowed by intent")
    if not isinstance(planner["params"], dict):
        raise ValueError("planner.params must be an object")
    planner["params"] = plugin.normalize_params(planner["params"], spec)
    if not isinstance(planner["params"], dict):
        raise ValueError("planner normalizer must return an object")

    execution = spec["execution"]
    if not isinstance(execution, dict):
        raise ValueError("execution must be an object")
    mode = execution.get("control_mode")
    if not isinstance(mode, str) or mode not in CONTROL_MODES:
        raise ValueError(f"execution.control_mode must be one of {list(CONTROL_MODES)}")
    exclusive = {"waypoint_barrier_v1": ("waypoint_hold_s",),
                 "semantic_phase_route_v1": ("terminal_hold_s", "async_timing_tolerance")}[mode]
    common = ("control_mode", "backend", "takeoff_alt_m", "speed_m_s", "arrival_tolerance_m",
              "confirmation_dwell_s", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s",
              "phase_timeout_override_s")
    _object(execution, f"execution ({mode})", common + exclusive, optional=("phase_timeout_override_s",))
    if "phase_timeout_override_s" in execution:
        _numeric(execution, "phase_timeout_override_s", "execution", .001, 3600)
    _enum(execution, "backend", "execution", ("AUTO",))
    for key, low, high in (("takeoff_alt_m", 3, 100), ("speed_m_s", .5, 15), ("arrival_tolerance_m", .2, 5),
            ("confirmation_dwell_s", 0, 60), ("record_hz", 1, 50), ("max_gap_s", .05, 5),
            ("min_separation_m", .1, 1000), ("timeout_s", 10, 3600), ("ready_timeout_s", 10, 300)):
        _numeric(execution, key, "execution", low, high)
    _numeric(execution, exclusive[0], "execution", 0, 60)
    if mode == "semantic_phase_route_v1":
        timing = _object(execution["async_timing_tolerance"], "async_timing_tolerance", ("min_s", "fraction_of_phase"))
        _numeric(timing, "min_s", "async_timing_tolerance", 0, 3600)
        _numeric(timing, "fraction_of_phase", "async_timing_tolerance", 0, 1)
    if execution["speed_m_s"] > platform["max_speed_m_s"]:
        raise ValueError("command speed exceeds platform max_speed_m_s")
    if not world["flight_up_bounds_m"][0] <= execution["takeoff_alt_m"] <= world["flight_up_bounds_m"][1]:
        raise ValueError("takeoff altitude outside flight_up_bounds_m")
    region = next(r for r in scenario["regions"] if r["id"] == mission["target_region_id"])
    if min(region["width_m"], region["height_m"]) <= 2 * execution["arrival_tolerance_m"]:
        raise ValueError("region too small for declared arrival tolerance")
    expected = scene_family_id(spec)
    if "family_id" in spec and spec["family_id"] != expected:
        raise ValueError(f"family_id does not match scene content: expected {expected}")
    if "family_scheme" in spec and spec["family_scheme"] != FAMILY_SCHEME:
        raise ValueError(f"family_scheme must be {FAMILY_SCHEME}")
    spec.update(family_id=expected, family_scheme=FAMILY_SCHEME)
    return spec


def _validate_plan(spec, plan, intent):
    agents = {v["id"] for v in spec["scenario"]["vehicles"]}
    if not isinstance(plan, PlanResult) or set(plan.routes) != agents or set(plan.assignments) != agents:
        raise ValueError("planner must return PlanResult with every agent exactly once")
    for agent, route in plan.routes.items():
        if not isinstance(route, dict) or set(route) != set(intent.semantic_phases):
            raise ValueError(f"planner route phases do not match intent: {agent}")
        for phase, points in route.items():
            if not isinstance(points, list):
                raise ValueError("planner phase route must be a list")
            if phase == "return" and not spec["mission"]["return_required"] and points:
                raise ValueError("planner emitted return route when return_required is false")
            for point in points:
                _object(point, "route point", ("east_m", "north_m"))
                for key in ("east_m", "north_m"):
                    number(point[key], f"route point.{key}", -2000, 2000)
    if not isinstance(plan.diagnostics, dict):
        raise ValueError("planner diagnostics must be an object")


def _compile_generic_barrier(spec, plan, intent):
    """Same legacy barrier mechanics for extension phases, no route backend."""
    execution = spec["execution"]
    agents = [v["id"] for v in spec["scenario"]["vehicles"]]
    previous = {v["id"]: {"east_m": v["east_m"], "north_m": v["north_m"]} for v in spec["scenario"]["vehicles"]}
    phases, mapping, by_semantic = [], {}, {}
    idle = {agent: 0 for agent in agents}
    for semantic in intent.semantic_phases:
        by_semantic[semantic] = []
        for index in range(max(len(plan.routes[agent][semantic]) for agent in agents)):
            name, targets, roles = f"leg_{len(phases):03d}", {}, {}
            for agent in agents:
                active = index < len(plan.routes[agent][semantic])
                point = plan.routes[agent][semantic][index] if active else previous[agent]
                targets[agent] = dict(point, up_m=execution["takeoff_alt_m"], speed_m_s=execution["speed_m_s"],
                                      hold_s=execution["waypoint_hold_s"])
                role = semantic if active else "idle_padding"
                roles[agent] = dict(role=role, service_enabled=active and semantic in intent.service_phases,
                                   partition_id=plan.assignments[agent])
                idle[agent] += int(not active)
                previous[agent] = point
            phases.append(dict(name=name, targets=targets))
            mapping[name] = dict(semantic_phase=semantic, agents=roles)
            by_semantic[semantic].append(name)
    if not 1 <= len(phases) <= 100:
        raise ValueError("route exceeds backend limit of 1 to 100 execution phases")
    return phases, dict(version="intent_semantics_v1", execution_phases=mapping,
                        service_activation="registered service phases only; padding disabled",
                        window_source="execution_events + compiled_semantic_plan"), by_semantic, idle


def compile_mission_v3(spec):
    from .capability import nominal_capability
    from .mission_planning import compile_execution_phases

    spec = normalize_v3(spec)
    intent, planner = get_intent(spec["mission"]["intent"]), get_planner(spec["planner"]["name"])
    plan = planner.plan_routes(copy.deepcopy(spec))
    _validate_plan(spec, plan, intent)
    if spec["execution"]["control_mode"] == "semantic_phase_route_v1":
        from .route_planning import compile_continuous_mission
        return compile_continuous_mission(spec, plan, intent, planner)
    if intent.name == "reconnaissance":
        phases, semantic, by_semantic, idle = compile_execution_phases(spec, plan.routes, plan.assignments)
    else:
        phases, semantic, by_semantic, idle = _compile_generic_barrier(spec, plan, intent)
    capability_spec = dict(spec, platform=spec["scenario"]["platform"],
                           planner=dict(tracking_margin_m=spec["planner"]["params"].get("tracking_margin_m", 0.0)))
    capability = nominal_capability(capability_spec, phases)
    scene = dict(schema_version=1, scenario_id=spec["task_id"], origin=copy.deepcopy(spec["scenario"]["origin"]),
                 vehicles=copy.deepcopy(spec["scenario"]["vehicles"]), phases=phases)
    for key in ("takeoff_alt_m", "record_hz", "max_gap_s", "min_separation_m", "timeout_s", "ready_timeout_s"):
        scene[key] = spec["execution"][key]
    scene = validate(scene)
    budget = capability["nominal_budget"]
    planning = dict(plan.diagnostics)
    planning.update(planner_name=planner.name, planner_version=planner.version, agent_to_partition=plan.assignments,
        per_agent_reference_routes=plan.routes, semantic_to_execution_phase_map=by_semantic,
        per_agent_path_length_m=budget["per_agent_path_length_m"], nominal_time_estimate_s=budget["total_time_estimate_s"],
        nominal_min_clearance_m=capability["nominal_min_clearance_m"], execution_phase_count=len(phases),
        idle_padding_steps=idle, feasibility_checks=capability, unverified_constraints=capability["unverified_constraints"],
        reference_time_semantics="event_driven_no_prescribed_arrival_times")
    scene.update(task_spec=spec, family_id=spec["family_id"], family_scheme=FAMILY_SCHEME,
                 control_mode=spec["execution"]["control_mode"], semantic_plan=semantic, planning=planning)
    return scene


def from_v2(spec, control_mode="waypoint_barrier_v1"):
    """Explicit authoring helper; reading a legacy task never migrates it implicitly."""
    from .mission_schema import normalize_mission
    value = normalize_mission(spec)
    value["schema_version"] = 3
    value.pop("family_id")
    value["scenario"]["platform"] = value.pop("platform")
    mission = value["mission"]
    mission["intent_params"] = {key: mission.pop(key) for key in ("objective", "coverage_required", "observation_model")}
    planner = value["planner"]
    value["planner"] = dict(name=planner.pop("name"), params=planner)
    value["execution"]["control_mode"] = control_mode
    if control_mode == "semantic_phase_route_v1":
        value["execution"]["terminal_hold_s"] = value["execution"].pop("waypoint_hold_s")
        value["execution"]["async_timing_tolerance"] = dict(min_s=3.0, fraction_of_phase=.2)
    return normalize_v3(value)
