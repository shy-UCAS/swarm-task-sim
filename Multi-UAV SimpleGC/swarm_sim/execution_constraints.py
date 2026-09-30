"""Sampled lifecycle resource limits, separate from geometric mission success."""

import math
from bisect import bisect_right
from itertools import combinations

from .mission_evaluation import EPS, position_valid, source_time, tri_and, window_evidence
from .observations import finite_number
from .recording import segment_distance
from .protocol import SHARED_CONSTRAINT_VERSION


CONSTRAINT_RULE_VERSION = SHARED_CONSTRAINT_VERSION


def _events(events, kind, agent, shift):
    return sorted((dict(event, host_s=event["t"] + shift) for event in events
                   if event.get("event") == kind and event.get("agent_id") == agent
                   and finite_number(event.get("t"))), key=lambda e: e["host_s"])


def _duration(start, end, model):
    left, right = source_time(start["host_s"], model), source_time(end["host_s"], model)
    if left is not None and right is not None:
        return right - left, "passive_FCU_source_seconds"
    a, b = start.get("source_boot_s"), end.get("source_boot_s")
    if finite_number(a) and finite_number(b) and b >= a:
        return b - a, "event_latest_FCU_source_seconds_proxy"
    return None, "source_duration_unavailable"


def _channel_limits(rows, start, end, ready, landing, world, platform, max_gap, allowance):
    evidence = window_evidence(rows, start, end, max_gap, edge_allowance=allowance)
    violations = []
    for stamp, point in evidence["points"]:
        east, north, up = point
        if not world["east_bounds_m"][0] - EPS <= east <= world["east_bounds_m"][1] + EPS:
            violations.append("east_bounds")
        if not world["north_bounds_m"][0] - EPS <= north <= world["north_bounds_m"][1] + EPS:
            violations.append("north_bounds")
        if up > world["flight_up_bounds_m"][1] + EPS:
            violations.append("upper_altitude_bounds")
    transitions_known = ready is not None and landing is not None and start <= ready <= landing <= end
    if transitions_known:
        cruise = window_evidence(rows, ready, landing, max_gap)
        if any(point[2] < world["flight_up_bounds_m"][0] - EPS for _, point in cruise["points"]):
            violations.append("cruise_lower_altitude_bounds")
    complete = evidence["complete"]
    length = sum(math.dist(a, b) for _, _, a, b in evidence["segments"])
    bounds_pass = False if violations else (True if complete and transitions_known else None)
    path_pass = False if length > platform["max_path_length_m"] + EPS else (True if complete else None)
    return dict(world_bounds_pass=bounds_pass, path_length_pass=path_pass,
                path_length_m=length, path_length_is_lower_bound=not complete,
                evidence_complete=complete, transition_events_complete=transitions_known,
                sampled_edge_allowance_s=allowance, violations=sorted(set(violations)),
                transition_lower_bound="not_applicable; flight_up minimum applies only to stabilized cruise",
                method="piecewise-linear sampled positions; no interpolation through invalid/gap intervals")


def _proxy_dynamics(rows, start, end, model, platform, max_gap):
    speeds, climbs, accelerations, source_intervals = [], [], [], 0
    previous = None
    for stamp, value in rows:
        if not start <= stamp <= end:
            continue
        if not position_valid(value) or len(value) < 6 or not all(finite_number(v) for v in value[3:6]):
            previous = None
            continue
        speeds.append(math.hypot(value[3], value[4]))
        climbs.append(abs(value[5]))
        source = source_time(stamp, model)
        if previous is not None and source is not None and previous[2] is not None:
            dt = source - previous[2]
            if 0 < stamp - previous[0] <= max_gap + EPS and dt > 0:
                accelerations.append(math.hypot(value[3] - previous[1][3], value[4] - previous[1][4]) / dt)
                source_intervals += 1
        previous = (stamp, value, source)
    return dict(status="evaluated_proxy" if accelerations else "not_verified", hard_gate=False,
                horizontal_speed_max_m_s=max(speeds) if speeds else None,
                vertical_speed_abs_max_m_s=max(climbs) if climbs else None,
                horizontal_acceleration_max_m_s2=max(accelerations) if accelerations else None,
                horizontal_speed_exceeds_nominal=any(x > platform["max_speed_m_s"] for x in speeds),
                vertical_speed_exceeds_nominal=any(x > platform["max_climb_rate_m_s"] for x in climbs),
                horizontal_acceleration_exceeds_nominal=any(x > platform["max_horizontal_accel_m_s2"] for x in accelerations),
                valid_difference_intervals=source_intervals, max_host_gap_s=max_gap,
                time_basis="passive_FCU_source_seconds", method="first difference of FCU estimated horizontal velocity",
                limitation="uncalibrated telemetry proxy, not SIM truth acceleration or a physical feasibility proof")


def _segment_position(segment, stamp):
    start, end, a, b = segment
    weight = (stamp - start) / (end - start) if end > start else 0.0
    return [a[k] + weight * (b[k] - a[k]) for k in range(3)]


def _lifecycle_separation(traces, agents, start, end, threshold, max_gap, allowance, lifecycle_complete):
    """Compare simultaneously observed motion, including grounded neighbours.

    Intersect independently valid segment intervals; never connect endpoints
    across an invalid sample. Isolated valid positions can prove a violation,
    but cannot make missing intervening motion safe.
    """
    evidence = {agent: window_evidence(traces.get(agent, []), start, end, max_gap, allowance)
                for agent in agents}
    pairs, minimum = [], None
    for left, right in combinations(agents, 2):
        a, b = evidence[left], evidence[right]
        a_segments, b_segments = a["segments"], b["segments"]
        index_a = index_b = 0
        pair_min, assessed, risks = None, 0, 0
        while index_a < len(a_segments) and index_b < len(b_segments):
            sa, sb = a_segments[index_a], b_segments[index_b]
            begin, finish = max(sa[0], sb[0]), min(sa[1], sb[1])
            if begin < finish:
                distance = segment_distance(_segment_position(sa, begin), _segment_position(sb, begin),
                                            _segment_position(sa, finish), _segment_position(sb, finish))
                pair_min = distance if pair_min is None else min(pair_min, distance)
                assessed += 1
                risks += int(distance < threshold)
            if sa[1] <= sb[1]:
                index_a += 1
            else:
                index_b += 1
        # Exact points remain evidence even if both adjacent segments are broken.
        point_maps = [{t: p for t, p in channel["points"]} for channel in (a, b)]
        segment_starts = [[segment[0] for segment in channel["segments"]] for channel in (a, b)]
        point_risks, assessed_points = set(), set()
        for side, other in ((0, 1), (1, 0)):
            other_segments = (a_segments, b_segments)[other]
            for stamp, point in point_maps[side].items():
                counterpart = point_maps[other].get(stamp)
                if counterpart is None:
                    index = bisect_right(segment_starts[other], stamp) - 1
                    if index >= 0 and other_segments[index][0] <= stamp <= other_segments[index][1]:
                        counterpart = _segment_position(other_segments[index], stamp)
                if counterpart is None:
                    continue
                assessed_points.add(stamp)
                distance = math.dist(point, counterpart)
                pair_min = distance if pair_min is None else min(pair_min, distance)
                if distance < threshold:
                    point_risks.add(stamp)
        complete = lifecycle_complete and a["complete"] and b["complete"] and (assessed > 0 or start == end)
        passed = False if risks or point_risks else (True if complete else None)
        pairs.append(dict(agents=[left, right], minimum_m=pair_min, passed=passed,
                          status="risk" if passed is False else ("clear_observed" if passed is True else "unknown"),
                          evidence_complete=complete, assessed_pair_intervals=assessed, risk_pair_intervals=risks,
                          assessed_simultaneous_points=len(assessed_points), risk_simultaneous_points=len(point_risks)))
        if pair_min is not None:
            minimum = pair_min if minimum is None else min(minimum, pair_min)
    passed = tri_and(pair["passed"] for pair in pairs)
    return dict(passed=passed, minimum_m=minimum, min_separation_m=threshold, per_pair=pairs,
                status="risk" if passed is False else ("clear_observed" if passed is True else "unknown"),
                fleet_window_s=[start, end], sampled_edge_allowance_s=allowance,
                method="simultaneous piecewise-linear relative motion, plus valid isolated positions; no invalid/gap bridging",
                scope="earliest armed_confirmed through latest landed for every pair, including grounded neighbours")


def evaluate_execution_constraints(scene, lifecycle_observations, lifecycle_truth, events,
                                   metadata, lifecycle_epoch, clocks=None):
    spec = scene["task_spec"]
    platform, world, execution = spec["platform"], spec["scenario"]["world"], spec["execution"]
    shift = metadata["run_epoch_monotonic_s"] - lifecycle_epoch
    clocks = clocks or metadata.get("lifecycle_clock_models", {})
    results = {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        armed = _events(events, "armed_confirmed", agent, shift)
        landed = _events(events, "landed", agent, shift)
        ready = _events(events, "airborne_ready", agent, shift)
        landing = _events(events, "landing_started", agent, shift)
        lifecycle_complete = bool(armed and landed and landed[-1]["host_s"] >= armed[0]["host_s"])
        first = armed[0] if armed else dict(host_s=shift)
        last = landed[-1] if landed else dict(host_s=metadata.get("elapsed_s", 0) + shift)
        if last["host_s"] < first["host_s"]:
            last = dict(host_s=max(first["host_s"], metadata.get("elapsed_s", 0) + shift))
        start, end = first["host_s"], last["host_s"]
        airborne_ready = ready[0]["host_s"] if ready else None
        landing_started = landing[0]["host_s"] if landing else None
        args = (start, end, airborne_ready, landing_started, world, platform,
                execution["max_gap_s"], 1 / execution["record_hz"])
        truth = _channel_limits(lifecycle_truth.get(agent, []), *args)
        observation = _channel_limits(lifecycle_observations.get(agent, []), *args)
        if not lifecycle_complete:
            for channel in (truth, observation):
                channel["evidence_complete"] = False
                channel["path_length_is_lower_bound"] = True
                for key in ("world_bounds_pass", "path_length_pass"):
                    if channel[key] is True:
                        channel[key] = None
        duration, basis = _duration(first, last, clocks.get(agent)) if lifecycle_complete else (None, "incomplete_lifecycle")
        duration_limit = platform["max_airborne_time_s"] - platform["reserve_time_s"]
        time_pass = duration <= duration_limit + EPS if duration is not None else None
        # Known violations from either independent position channel reject the
        # episode. Both channels must be complete before declaring limits met.
        bounds = tri_and([truth["world_bounds_pass"], observation["world_bounds_pass"]])
        path = tri_and([truth["path_length_pass"], observation["path_length_pass"]])
        results[agent] = dict(hard_constraints_pass=tri_and([bounds, path, time_pass]),
                             world_bounds_pass=bounds, path_length_pass=path, airborne_time_pass=time_pass,
                             truth=truth, observation=observation,
                             armed_to_landed_host_s=end - start, armed_to_landed_source_s=duration,
                             duration_time_basis=basis, duration_proxy="armed_confirmed_to_landed; includes ground margins",
                             lifecycle_complete=lifecycle_complete,
                             reason="complete_lifecycle" if lifecycle_complete else "incomplete_armed_to_landed_lifecycle",
                             available_airborne_budget_s=duration_limit, reserve_time_s=platform["reserve_time_s"],
                             lifecycle_window_s=[start, end],
                             proxy_dynamics=_proxy_dynamics(lifecycle_observations.get(agent, []), start, end,
                                                           clocks.get(agent), platform, execution["max_gap_s"]))
    fleet_start = min(r["lifecycle_window_s"][0] for r in results.values())
    fleet_end = max(r["lifecycle_window_s"][1] for r in results.values())
    boundary_complete = all(r["lifecycle_complete"] for r in results.values())
    separation_args = (list(results), fleet_start, fleet_end, execution["min_separation_m"],
                       execution["max_gap_s"], 1 / execution["record_hz"], boundary_complete)
    truth_separation = _lifecycle_separation(lifecycle_truth, *separation_args)
    observation_separation = _lifecycle_separation(lifecycle_observations, *separation_args)
    separation_pass = tri_and([truth_separation["passed"], observation_separation["passed"]])
    for agent, result in results.items():
        result["lifecycle_separation_pass"] = tri_and(pair["passed"] for channel in (truth_separation, observation_separation)
                                                       for pair in channel["per_pair"] if agent in pair["agents"])
        result["hard_constraints_pass"] = tri_and([result["hard_constraints_pass"], result["lifecycle_separation_pass"]])
    return dict(schema_version=1, constraint_validation_version=CONSTRAINT_RULE_VERSION,
                hard_constraints_pass=tri_and([*(r["hard_constraints_pass"] for r in results.values()), separation_pass]),
                per_agent=results, lifecycle_separation_pass=separation_pass,
                lifecycle_separation=dict(truth=truth_separation, observation=observation_separation),
                scope="armed-confirmed through landed, separate from the exported mission observation window",
                bounds_semantics="horizontal and upper-altitude limits throughout; lower flight_up bound only from airborne_ready through landing_started; transition lower bound not applicable",
                hard_constraints=["world_bounds", "executed_path_length", "airborne_time_with_reserve", "lifecycle_pair_separation"],
                unverified_constraints=["calibrated_physical_acceleration", "battery_electrochemistry", "collision_physics"],
                numerical_evidence="sampled piecewise-linear proxy; passive source mapping is not physical lockstep")
