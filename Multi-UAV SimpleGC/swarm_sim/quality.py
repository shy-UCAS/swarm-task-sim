"""Versioned quality policy, distinct from vehicle capability and clock accuracy."""

import hashlib
import json
import math


DEFAULT_POLICY = {
    "version": "0.2.2",
    "clock_strict_p95_s": 0.02,
    "clock_acceptable_p95_s": 0.05,
    "horizontal_velocity_sanity_m_s": 50.0,
    "vertical_velocity_sanity_m_s": 30.0,
    "horizontal_position_bound_m": 2500.0,
    "min_up_m": -100.0,
    "max_up_m": 200.0,
    "min_observation_valid_fraction": 0.99,
    "min_truth_valid_fraction": 0.99,
    "observation_filter": "global_position_v1",
    "invalid_sample_interpolation": "barrier",
}


def resolve_policy(overrides=None):
    policy = dict(DEFAULT_POLICY)
    if overrides is not None:
        if not isinstance(overrides, dict) or set(overrides) - set(policy):
            raise ValueError("quality policy must be an object with supported fields")
        policy.update(overrides)
    if not isinstance(policy["version"], str) or not policy["version"].strip():
        raise ValueError("quality policy version must be a nonempty string")
    for key, default in DEFAULT_POLICY.items():
        value = policy[key]
        if isinstance(default, float):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"quality policy {key} must be a finite number")
            policy[key] = float(value)
    for key in ("clock_strict_p95_s", "clock_acceptable_p95_s", "horizontal_velocity_sanity_m_s",
                "vertical_velocity_sanity_m_s", "horizontal_position_bound_m"):
        if policy[key] <= 0:
            raise ValueError(f"quality policy {key} must be positive")
    if policy["clock_strict_p95_s"] > policy["clock_acceptable_p95_s"]:
        raise ValueError("strict clock threshold must not exceed acceptable threshold")
    if policy["min_up_m"] >= policy["max_up_m"]:
        raise ValueError("invalid altitude sanity interval")
    for key in ("min_observation_valid_fraction", "min_truth_valid_fraction"):
        if not 0 < policy[key] <= 1:
            raise ValueError(f"quality policy {key} must be in (0, 1]")
    for key in ("observation_filter", "invalid_sample_interpolation"):
        if policy[key] != DEFAULT_POLICY[key]:
            raise ValueError(f"unsupported {key}")
    return policy


def policy_hash(policy):
    normalized = resolve_policy(policy)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def clock_grade(model, policy):
    residual = model.get("receive_residual_abs_p95_s")
    if (not model.get("available") or isinstance(residual, bool) or
            not isinstance(residual, (int, float)) or not math.isfinite(residual) or residual < 0):
        return "unknown"
    if residual <= policy["clock_strict_p95_s"]:
        return "strict"
    if residual <= policy["clock_acceptable_p95_s"]:
        return "acceptable"
    return "failed"


def summarize_clocks(clocks, policy):
    per_agent = {agent: clock_grade(model, policy) for agent, model in clocks.items()}
    grades = list(per_agent.values())
    # A known failed vehicle suffices to reject the run even if another is unknown.
    overall = ("failed" if "failed" in grades else "unknown" if not grades or "unknown" in grades
               else "acceptable" if "acceptable" in grades else "strict")
    return dict(overall=overall, per_agent=per_agent,
                metric="heldout_host_receive_residual_p95; not an absolute synchronization bound")


def eligibility(quality, mission_success):
    other_checks = (quality["data_quality_pass"] and quality["truth_available_pass"] and
                    quality["run_completed"] and quality["separation_status"] == "clear_observed" and
                    quality["truth_separation"]["status"] == "clear_observed" and mission_success is True)
    grade = quality["clock_quality"]["overall"]
    return dict(benchmark_eligible=bool(other_checks and grade in ("strict", "acceptable")),
                strict_benchmark_eligible=bool(other_checks and grade == "strict"))


def episode_quality_eligibility(quality):
    """V3 data qualification, deliberately independent of mission outcome."""
    return bool(all(quality.get(k) is True for k in ("run_completed", "data_quality_pass", "truth_available_pass",
                     "timing_diagnostic_pass", "execution_constraints_pass"))
                and quality.get("clock_quality", {}).get("overall") in ("strict", "acceptable")
                and quality.get("separation_status") == "clear_observed"
                and quality.get("truth_separation", {}).get("status") == "clear_observed")


def v3_eligibility(quality, labels):
    """Append data qualification while retaining the existing shared benchmark meaning."""
    result = eligibility(quality, labels["mission_success"])
    additional = (quality.get("execution_constraints_pass") is True and labels.get("semantic_consistency") == "agree"
                  and labels.get("mission_success_observation") is True)
    result["benchmark_eligible"] &= additional
    result["strict_benchmark_eligible"] &= additional
    result["episode_quality_eligible"] = episode_quality_eligibility(quality)
    return result


def invalid_intervals(traces, maximum_gap_s, flags=None):
    """Closed sample-support intervals for future window consumers; no window qualification."""
    if not isinstance(maximum_gap_s, (int,float)) or isinstance(maximum_gap_s,bool) or not math.isfinite(maximum_gap_s) or maximum_gap_s <= 0:
        raise ValueError("maximum_gap_s must be finite and positive")
    result = {}
    flags = flags or {}
    for agent, rows in traces.items():
        intervals, previous = [], None
        for stamp, value in rows:
            if not isinstance(stamp,(int,float)) or isinstance(stamp,bool) or not math.isfinite(stamp):
                raise ValueError("invalid interval source timestamp")
            if previous is not None and stamp <= previous:
                raise ValueError("interval evidence must be strictly increasing")
            if previous is not None and stamp-previous > maximum_gap_s:
                intervals.append(dict(start_s=previous,end_s=stamp,reason="sample_gap"))
            reason = flags.get(agent, {}).get(stamp)
            valid = value is not None and len(value) >= 6 and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in value[:6])
            if not valid or reason:
                intervals.append(dict(start_s=stamp,end_s=stamp,reason=str(reason or "invalid_observation")))
            previous = stamp
        # Invalid samples are barriers. Adjacent invalid samples of the same reason may be grouped.
        merged = []
        for row in intervals:
            if (merged and row["reason"] == merged[-1]["reason"] and row["start_s"]-merged[-1]["end_s"] <= maximum_gap_s
                    and not any(merged[-1]["end_s"] < t < row["start_s"] and v is not None for t,v in rows)):
                merged[-1]["end_s"] = row["end_s"]
            else:
                merged.append(dict(row))
        result[agent] = merged
    return result
