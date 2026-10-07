"""Versioned r1.2b diagnostics and per-stage rolling anomaly accounting.

Physical/infrastructure controllers own firmware identities, protected hashes,
infrastructure and disk gates. This module never mutates quality or old r1.2
assessments and never treats an unknown semantic result as a failed task.
"""

from .validation_policy import assess_run as assess_r12, finite, zero_length_segments


VERSION = "v05_acceptance_r1_2b"
ROLLING_VERSION = "v05_rolling_anomalies_r1_2b"


def assess_run(scene, metadata, quality, labels, metrics, ac4, onboard, *, stage="pilot"):
    if stage not in ("pilot", "batch"):
        raise ValueError("r1.2b acceptance applies only to pilot and batch")
    prior = assess_r12(scene, metadata, quality, labels, metrics, ac4, onboard, stage=stage)
    checks = {key: prior["hard_checks"][key] for key in
              ("parameter_firmware", "onboard_mission_parameters")}
    separation = quality.get("truth_separation", {})
    minimum, required = separation.get("minimum_m"), scene.get("min_separation_m")
    violation = (separation.get("status") == "risk" or
                 finite(minimum) and finite(required) and minimum < required)
    checks["truth_separation"] = not violation
    anomalies, semantic_flags, reasons = [], [], []

    def mark(target, code, value, *, channel=None, agent=None, reason=None):
        target.append(dict(code=code, channel=channel, agent_id=agent, value=value, reason=reason))

    if not (finite(minimum) and finite(required) and separation.get("status") == "clear_observed") and not violation:
        mark(anomalies, "truth_separation_unknown", separation,
             reason="no_known_violation; retain_unassessed_evidence")
    for channel, field in (("truth", "mission_success"), ("observation", "mission_success_observation")):
        success = labels.get(field)
        if success is False:
            reasons.append("task_failure_" + channel)
            mark(semantic_flags, "task_failure", False, channel=channel)
        elif success is not True:
            mark(anomalies, "task_result_unknown", success, channel=channel)
    consistency = labels.get("semantic_consistency")
    truth, observation = labels.get("mission_success"), labels.get("mission_success_observation")
    if consistency == "disagree" or (type(truth) is bool and type(observation) is bool and truth != observation):
        reasons.append("label_disagreement")
        mark(semantic_flags, "label_disagreement", consistency)
    elif consistency != "agree":
        mark(anomalies, "label_consistency_unknown", consistency)
    eligible = quality.get("episode_quality_eligible")
    if eligible is False:
        reasons.append("episode_quality_ineligible")
        mark(semantic_flags, "episode_quality_ineligible", False)
    elif eligible is not True:
        mark(anomalies, "episode_quality_unknown", eligible)
    zero = zero_length_segments(scene)
    if zero != 0:
        mark(anomalies, "zero_length_segments" if zero is not None else "route_geometry_unknown", zero)
    if metadata.get("status") != "completed":
        mark(anomalies, "run_not_completed", metadata.get("status"),
             reason="controller_classifies_infrastructure_independently")
    if quality.get("analysis_error"):
        mark(anomalies, "analysis_error", quality["analysis_error"])
    mission = scene.get("task_spec", {}).get("mission", {})
    if mission.get("intent") == "patrol":
        planned = mission.get("intent_params", {}).get("laps")
        for channel in ("truth", "observation"):
            evidence = labels.get("mission_metrics", {}).get(channel, {})
            laps = evidence.get("per_agent_laps_observed", {}) or {}
            progress = evidence.get("perimeter_revisit", {}).get("per_agent_progress", {})
            for vehicle in scene["vehicles"]:
                agent = vehicle["id"]
                count = laps.get(agent)
                if count is not None and (type(count) is not int or
                        progress.get(agent, {}).get("evidence_complete") is not True):
                    mark(anomalies, "patrol_lap_evidence_inconsistent", count, channel=channel, agent=agent)
                elif count is not None and count != planned:
                    mark(semantic_flags, "patrol_laps_mismatch", count, channel=channel, agent=agent,
                         reason=f"planned_laps={planned}")
    failures = [name for name, passed in checks.items() if passed is not True]
    return dict(version=VERSION, stage=stage, hard_checks=checks, hard_failures=failures,
                soft_flags=prior["soft_flags"], semantic_flags=semantic_flags, new_anomalies=anomalies,
                individual_pass=not failures, episode_quality_eligible=eligible,
                soft_flags_affect_episode_quality=False,
                aggregate_anomaly=bool(reasons), aggregate_anomaly_reasons=reasons,
                external_checks_required=["frozen_input_and_firmware_identity", "protected_file_hashes",
                                          "infrastructure_and_disk"])


def assess_recent_runs(records, *, stage="pilot"):
    """Count distinct anomalous runs in this stage's last at most 20 runs.

    Callers pass only the rule-effective ledger (PP09 onward for pilot). Stage
    filtering starts batch independently. Duplicate run IDs occupy one slot;
    their known anomaly reasons are unioned without converting unknowns.
    """
    if stage not in ("pilot", "batch"):
        raise ValueError("unsupported r1.2b rolling stage")
    distinct = {}
    for record in records:
        assessment = record.get("assessment", {})
        record_stage = record.get("stage", assessment.get("stage"))
        if record_stage != stage:
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("rolling assessment requires a nonempty run_id")
        if assessment.get("version") != VERSION or assessment.get("stage") != stage:
            raise ValueError("rolling assessment requires the matching r1.2b policy and stage")
        reasons = assessment.get("aggregate_anomaly_reasons")
        if (not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons)
                or assessment.get("aggregate_anomaly") is not bool(reasons)):
            raise ValueError("inconsistent rolling anomaly assessment")
        row = distinct.setdefault(run_id, dict(run_id=run_id, reasons=[]))
        row["reasons"] = sorted(set(row["reasons"]) | set(reasons))
    window = list(distinct.values())[-20:]
    abnormal = sum(bool(row["reasons"]) for row in window)
    return dict(version=ROLLING_VERSION, stage=stage, effective_runs=len(distinct), window_limit=20,
                window_count=len(window), anomaly_count=abnormal, stop_threshold=5,
                stop=abnormal >= 5, runs=window, run_deduplication="run_id",
                anomaly_rule="any_channel_task_failure OR label_disagreement OR episode_quality_ineligible")
