"""Explicit r1.2 acceptance diagnostics; never change numerical data eligibility.

Historical r1 assessments are immutable. Controllers additionally verify frozen
inputs, firmware identities, protected files and infrastructure/retry budgets.
"""
import math

from .run_provenance import PARAMETER_COMPARISON_VERSION

VERSION = "v05_acceptance_r1_2"


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def zero_length_segments(scene):
    count = 0
    for phase in scene.get("phases", []):
        roles = scene.get("semantic_plan", {}).get("execution_phases", {}).get(phase.get("name"), {}).get("agents", {})
        for vehicle in scene.get("vehicles", []):
            agent = vehicle["id"]
            route = phase.get("routes", {}).get(agent)
            start = roles.get(agent, {}).get("start_point")
            if not isinstance(route, list) or not isinstance(start, dict):
                return None
            try:
                points = [tuple(p[k] for k in ("east_m", "north_m", "up_m")) for p in [start, *route]]
                if not all(all(finite(v) for v in point) for point in points):
                    return None
                count += sum(math.dist(a, b) <= 1e-9 for a, b in zip(points, points[1:]))
            except (KeyError, TypeError):
                return None
    return count if scene.get("phases") else None


def assess_run(scene, metadata, quality, labels, metrics, ac4, onboard, *, stage="validation"):
    if stage not in ("validation", "pilot", "batch"):
        raise ValueError("unsupported r1.2 acceptance stage")
    agents = {v["id"] for v in scene["vehicles"]}
    prov = metadata.get("run_provenance", {})
    readback = prov.get("parameter_evidence", {}).get("per_agent", {})
    parameters_ok = (prov.get("status") == "verified_before_takeoff"
        and prov.get("parameter_comparison_version") == PARAMETER_COMPARISON_VERSION
        and metadata.get("parameter_comparison_version") == PARAMETER_COMPARISON_VERSION
        and bool(metadata.get("binary_firmware", {}).get("sha256"))
        and bool(metadata.get("parameters_sha256"))
        and set(readback) == agents
        and all(row.get("complete") is True and row.get("status") == "complete"
                and type(row.get("received_count")) is int and row["received_count"] > 0
                and row["received_count"] == row.get("parameter_count")
                and row.get("missing_indices") == [] for row in readback.values()))
    separation = quality.get("truth_separation", {})
    minimum, required = separation.get("minimum_m"), scene.get("min_separation_m")
    zero = zero_length_segments(scene)
    checks = dict(parameter_firmware=parameters_ok,
        onboard_mission_parameters=onboard.get("pass_gate") is True and onboard.get("status") == "pass",
        truth_separation=finite(minimum) and finite(required) and minimum >= required
            and separation.get("status") == "clear_observed",
        no_zero_length_segments=zero == 0,
        run_completed=metadata.get("status") == "completed" and not quality.get("analysis_error"))
    if stage == "validation":
        checks["dual_channel_mission_success"] = (labels.get("mission_success") is True
            and labels.get("mission_success_observation") is True
            and labels.get("semantic_consistency") == "agree")
        checks["validation_episode_quality"] = quality.get("episode_quality_eligible") is True
    else:
        # A known unsuccessful mission remains an honest failure label. Missing
        # or contradictory outcomes cannot be assumed harmless (r1.2 item 8).
        checks["known_consistent_labels"] = (type(labels.get("mission_success")) is bool
            and type(labels.get("mission_success_observation")) is bool
            and labels.get("semantic_consistency") == "agree")
    flags = []
    def flag(code, status, value=None, threshold=None, *, channel=None, phase=None, agent=None, reason=None, **extra):
        flags.append(dict(code=code, status=status, channel=channel, phase=phase,
                          agent_id=agent, value=value, threshold=threshold, reason=reason, **extra))
    intermediate = metrics.get("intermediate_waypoints", {})
    rate = intermediate.get("stop_rate")
    if not finite(rate) or intermediate.get("unknown_count", 0):
        flag("AV-1", "unknown", rate, .1, channel="observation", reason="incomplete_intermediate_waypoint_evidence")
    elif rate > .1:
        flag("AV-1", "exceeded", rate, .1, channel="observation")
    limit = len({p.get("semantic_phase") for p in scene.get("phases", [])}) + 1
    per_agent = metrics.get("thresholds", {}).get("0.3", {}).get("per_agent", {})
    for agent in sorted(agents):
        row = per_agent.get(agent, {})
        count = row.get("stop_count")
        if not finite(count) or row.get("evidence_complete") is not True:
            flag("AV-2", "unknown", count, limit, channel="observation", agent=agent)
        elif count > limit:
            flag("AV-2", "exceeded", count, limit, channel="observation", agent=agent)
    for channel in ("truth", "observation"):
        phases = ac4.get("channels", {}).get(channel, {}).get("per_phase", {})
        for phase in scene.get("phases", []):
            row = phases.get(phase["name"], {})
            for key, source in (("primary", "primary"), ("crosscheck", "event_crosscheck")):
                comparison = row.get(key, {})
                d, tau = comparison.get("D_s"), comparison.get("tau_s")
                if not finite(d) or not finite(tau) or comparison.get("complete") is not True:
                    flag("AC4", "unknown", d, tau, channel=channel, phase=phase["name"], source=source)
                elif d > tau:
                    flag("AC4", "exceeded", d, tau, channel=channel, phase=phase["name"], source=source)
    mission = scene.get("task_spec", {}).get("mission", {})
    if mission.get("intent") == "patrol":
        planned = mission.get("intent_params", {}).get("laps")
        checks["known_patrol_laps_match"] = type(planned) is int
        for channel in ("truth", "observation"):
            evidence = labels.get("mission_metrics", {}).get(channel, {})
            laps = evidence.get("per_agent_laps_observed", {}) or {}
            progress = evidence.get("perimeter_revisit", {}).get("per_agent_progress", {})
            for agent in sorted(agents):
                count = laps.get(agent)
                complete = progress.get(agent, {}).get("evidence_complete") is True
                if count is None:
                    flag("AV-8", "unknown", None, planned, channel=channel, phase="patrol", agent=agent)
                elif type(count) is not int or not complete:
                    checks["patrol_lap_evidence_consistent"] = False
                elif count != planned:
                    checks["known_patrol_laps_match"] = False
    failures = [name for name, passed in checks.items() if passed is not True]
    return dict(version=VERSION, stage=stage, hard_checks=checks,
                hard_failures=failures, soft_flags=flags, individual_pass=not failures,
                episode_quality_eligible=quality.get("episode_quality_eligible"),
                soft_flags_affect_episode_quality=False,
                external_checks_required=["frozen_input_and_firmware_identity", "protected_file_hashes", "infrastructure_and_disk"])
