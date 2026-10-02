"""Intent-aware, evidence-only audit of frozen v3 exports; never replan/run.

Only manifest-bound files are used. Missing data stay null, with explicit
expected/available counts. Counterfactual completeness means quality eligible,
not mission successful, and never constitutes classification accuracy.
"""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .dataset_audit import _content_hash, _distribution, _rate, _read
from .episode_loader import load_episode
from .generation import canonical_hash, checked_path, file_hash
from .protocol import manifest_protocol
from .registry import get_intent


AUDIT_VERSION = "multi_intent_dataset_audit_v1"
COMMON_METRICS = (
    "episode_duration_s", "vehicle_count", "observation_valid_fraction", "truth_valid_fraction",
    "region_width_m", "region_height_m", "spawn_east_span_m", "spawn_north_span_m", "speed_m_s",
    "executed_path_length_m", "planned_path_length_m", "airborne_time_s", "executed_stage_count",
    "barrier_wait_s", "execution_stop_count", "execution_intermediate_stop_count",
    "execution_semantic_endpoint_stop_count", "execution_other_stop_count",
    "execution_fleet_stop_event_count", "execution_common_overlap_event_count", "execution_stationary_time_fraction",
    "execution_synchronized_time_fraction", "execution_common_overlap_event_fraction",
    "execution_intermediate_waypoint_stop_rate", "execution_arrival_lag_median_s",
    "execution_barrier_wait_median_s", "execution_nominal_timing_deviation_max_abs_s",
    "execution_05_stop_count", "execution_05_stationary_time_fraction", "execution_05_synchronized_time_fraction",
)


def _numeric(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _summary(values):
    result = _distribution(values)
    result.update(expected_values=len(values), missing_values=len(values)-result["count"])
    return result


def _numeric_leaves(value):
    if _numeric(value):
        return [value]
    if isinstance(value, dict):
        return [number for child in value.values() for number in _numeric_leaves(child)]
    if isinstance(value, list):
        return [number for child in value for number in _numeric_leaves(child)]
    return []


def _named_metric(tree, name):
    """Find registered metric keys without embedding any specific intent names."""
    if not isinstance(tree, dict):
        return []
    found = []
    for key, value in tree.items():
        if key == name:
            found.extend(_numeric_leaves(value))
        elif isinstance(value, dict):
            found.extend(_named_metric(value, name))
    return found


def id_position_order(vehicles):
    """Pairwise lexicographic ID agreement; tied coordinates are unevaluable."""
    ordered = sorted(vehicles, key=lambda vehicle: vehicle["id"])
    result = {}
    for axis in ("east", "north"):
        agree = comparable = tied = 0
        for i, first in enumerate(ordered):
            for second in ordered[i+1:]:
                delta = second[f"{axis}_m"] - first[f"{axis}_m"]
                if abs(delta) <= 1e-6:
                    tied += 1
                else:
                    comparable += 1
                    agree += delta > 0
        result[axis] = dict(agree_pairs=agree, comparable_pairs=comparable, tied_pairs=tied,
                            fully_ordered=(agree == comparable) if comparable else None)
    return result


def _aggregate_order(samples):
    result = {}
    for axis in ("east", "north"):
        values = [sample["id_position_order"][axis] for sample in samples]
        result[axis] = dict(pairwise=_rate(sum(v["agree_pairs"] for v in values),
            sum(v["comparable_pairs"] for v in values), "all non-tied agent pairs ordered lexicographically by ID"),
            episodes_fully_ordered=_rate(sum(v["fully_ordered"] is True for v in values),
                sum(v["fully_ordered"] is not None for v in values), "episodes with at least one non-tied pair"),
            tied_pairs=sum(v["tied_pairs"] for v in values))
    return result


def _topology(samples):
    counts = Counter(s["topology_token"] for s in samples if s["topology_token"] is not None)
    train = {s["topology_token"] for s in samples if s["split"] == "train" and s["topology_token"] is not None}
    test = [s["topology_token"] for s in samples if s["split"] == "test" and s["topology_token"] is not None]
    test_unique = set(test)
    return dict(signature_counts=dict(counts), missing_signature_episodes=sum(s["topology_token"] is None for s in samples),
        test_signature_seen_in_train=_rate(sum(t in train for t in test), len(test), "test episodes with available signatures; intent+mode scoped"),
        distinct_test_signatures_seen_in_train=_rate(len(test_unique & train), len(test_unique), "distinct available test signatures; intent+mode scoped"),
        test_missing_signature_episodes=sum(s["split"] == "test" and s["topology_token"] is None for s in samples))


def _metric_values(task, manifest, quality, constraints, allocation, windows, execution, agents):
    values = {name: [] for name in COMMON_METRICS}
    scenario = task["scenario"]
    target = next((region for region in scenario["regions"] if region["id"] == task["mission"]["target_region_id"]), {})
    for name, value in (("episode_duration_s", manifest.get("duration_s")), ("vehicle_count", len(agents)),
                        ("region_width_m", target.get("width_m")), ("region_height_m", target.get("height_m")),
                        ("speed_m_s", task["execution"].get("speed_m_s"))):
        values[name].append(value)
    for axis in ("east", "north"):
        coordinates = [v[f"{axis}_m"] for v in scenario["vehicles"]]
        values[f"spawn_{axis}_span_m"].append(max(coordinates)-min(coordinates) if coordinates else None)
    for agent in agents:
        for name in ("observation_valid_fraction", "truth_valid_fraction"):
            values[name].append(quality.get(name, {}).get(agent))
        per_agent = constraints.get("per_agent", {}).get(agent, {})
        values["executed_path_length_m"].append(per_agent.get("truth", {}).get("path_length_m"))
        values["airborne_time_s"].append(per_agent.get("armed_to_landed_source_s"))
        values["planned_path_length_m"].append(allocation.get("per_agent_path_length_m", {}).get(agent))
        for threshold, prefix in (("0.3", "execution"), ("0.5", "execution_05")):
            agent_metric = execution.get("thresholds", {}).get(threshold, {}).get("per_agent", {}).get(agent, {})
            complete_count = not agent_metric.get("stop_count_is_lower_bound", False) and not agent_metric.get("invalid_reason")
            values[prefix+"_stop_count"].append(agent_metric.get("stop_count") if complete_count else None)
            if threshold == "0.3":
                counts = agent_metric.get("counts_by_location") or {}
                for metric, location in (("intermediate", "intermediate_waypoint"),
                                         ("semantic_endpoint", "semantic_endpoint"), ("other", "other")):
                    values[f"execution_{metric}_stop_count"].append(counts.get(location) if complete_count else None)
    window_rows = windows.get("windows", [])
    stages = {w["phase"] for w in window_rows if isinstance(w, dict) and isinstance(w.get("phase"), str)}
    values["executed_stage_count"].append(len(stages) if stages else None)
    values["barrier_wait_s"].extend([w.get("barrier_wait_host_s") for w in window_rows] or [None])
    for threshold, prefix in (("0.3", "execution"), ("0.5", "execution_05")):
        table = execution.get("thresholds", {}).get(threshold, {})
        for key in ("stationary_time_fraction", "synchronized_time_fraction"):
            values[prefix+"_"+key].append(table.get(key))
    values["execution_common_overlap_event_fraction"].append(execution.get("thresholds", {}).get("0.3", {}).get("common_overlap_event_fraction"))
    for metric in ("fleet_stop_event_count", "common_overlap_event_count"):
        values["execution_"+metric].append(execution.get("thresholds", {}).get("0.3", {}).get(metric))
    values["execution_intermediate_waypoint_stop_rate"].append(execution.get("intermediate_waypoints", {}).get("stop_rate"))
    for name in ("arrival_lag", "barrier_wait"):
        values[f"execution_{name}_median_s"].append(execution.get(name+"_s", {}).get("distribution", {}).get("median"))
    values["execution_nominal_timing_deviation_max_abs_s"].append(execution.get("nominal_timing_deviation_s", {}).get("max_abs_s"))
    return values


def audit_dataset_v3(dataset_path, generation_manifest=None, attempt_ledger=None):
    root = Path(dataset_path).resolve()
    dataset = _read(root/"dataset_manifest.json")
    entries = dataset["episodes"]
    generation = _read(Path(generation_manifest), {}) if generation_manifest else {}
    ledger = _read(Path(attempt_ledger), {}) if attempt_ledger else {}
    samples, groups, family_splits, input_hashes = [], defaultdict(list), defaultdict(set), Counter()
    seen_runs, issues = set(), []
    for entry in entries:
        if entry["run_id"] in seen_runs:
            raise ValueError("duplicate run ID in dataset audit")
        seen_runs.add(entry["run_id"])
        episode_root = checked_path(root, entry["directory"])
        if file_hash(episode_root/"manifest.json") != entry["analysis_manifest_sha256"]:
            raise ValueError("dataset episode manifest changed")
        episode = load_episode(episode_root)
        manifest = _read(episode_root/"manifest.json")
        if manifest_protocol(manifest)["task_kind"] != "mission_v3":
            raise ValueError("v3 audit cannot mix semantic protocols")
        def evidence(name):
            return (_read(episode_root/name, {}) or {}) if name in manifest["artifact_sha256"] else {}
        task, quality = evidence("task.json"), evidence("quality.json")
        allocation, windows = evidence("allocation.json"), evidence("phase_windows.json")
        execution_raw, constraints = evidence("execution_metrics.json"), evidence("execution_constraints.json")
        execution_usable = execution_raw.get("version") == "execution_artifacts_v1"
        execution = execution_raw if execution_usable else {}
        labels = episode["targets"]
        intent_name, mode = task["mission"]["intent"], task["execution"]["control_mode"]
        intent = get_intent(intent_name)
        truth_metrics = labels.get("mission_metrics", {}).get("truth", {}) or evidence("semantic_validation.json").get("truth", {})
        specific = {name: _named_metric(truth_metrics, name) or [None] for name in intent.required_audit_metrics}
        common = _metric_values(task, manifest, quality, constraints, allocation, windows, execution, episode["agent_ids"])
        signature, signature_error = None, None
        if intent.topology_signature is not None:
            if not allocation:
                signature_error = "missing manifest-bound allocation.json"
            else:
                try:
                    signature = intent.topology_signature(task, allocation)
                    canonical_hash(signature)  # reject NaN/unserializable signatures
                except (KeyError, ValueError, TypeError) as exc:
                    signature_error = f"{type(exc).__name__}: {exc}"
        else:
            signature_error = "intent provides no topology_signature"
        family, split = entry.get("family_id"), entry.get("split")
        if family:
            family_splits[family].add(split)
        input_hashes[_content_hash(task)] += 1
        sample = dict(run_id=entry["run_id"], family_id=family, split=split, intent=intent_name, control_mode=mode,
            mission_success=labels.get("mission_success"), episode_quality_eligible=quality.get("episode_quality_eligible"),
            benchmark_eligible=manifest.get("benchmark_eligible"), strict_benchmark_eligible=manifest.get("strict_benchmark_eligible"),
            run_status=manifest.get("run_status"), frames=len(episode["t_s"]), agents=len(episode["agent_ids"]),
            clock_grade=quality.get("clock_quality", {}).get("overall", "unknown"),
            metrics=common, intent_metrics=specific,
            required_audit_metrics=list(intent.required_audit_metrics),
            missing_common_metrics=[name for name, values in common.items() if not any(_numeric(v) for v in values)],
            missing_intent_metrics=[name for name, values in specific.items() if not any(_numeric(v) for v in values)],
            execution_metrics_version=execution_raw.get("version"), execution_metrics_available=bool(execution_raw),
            execution_metrics_usable=execution_usable,
            execution_metrics_error=(None if execution_usable else
                ("unsupported execution metrics version" if execution_raw else "missing manifest-bound execution_metrics.json")),
            execution_lower_bound_stop_counts={threshold: {agent: value.get("stop_count")
                for agent, value in summary.get("per_agent", {}).items() if value.get("stop_count_is_lower_bound") is True}
                for threshold, summary in execution.get("thresholds", {}).items()},
            id_position_order=id_position_order(task["scenario"]["vehicles"]),
            topology_signature=signature, topology_signature_error=signature_error,
            topology_token=canonical_hash([intent_name, mode, signature]) if signature is not None else None)
        samples.append(sample)
        groups[intent_name, mode].append(sample)
    group_reports = []
    for (intent_name, mode), members in sorted(groups.items()):
        common = {name: _summary([v for m in members for v in m["metrics"][name]]) for name in COMMON_METRICS}
        required = get_intent(intent_name).required_audit_metrics
        specific = {name: _summary([v for m in members for v in m["intent_metrics"][name]]) for name in required}
        group_reports.append(dict(intent=intent_name, control_mode=mode, episode_count=len(members),
            metrics=common, intent_metrics=specific, required_audit_metrics=list(required),
            missing_common_metrics=[name for name, d in common.items() if not d["count"]],
            missing_intent_metrics=[name for name, d in specific.items() if not d["count"]],
            clock_grades=dict(Counter(m["clock_grade"] for m in members)), id_position_order=_aggregate_order(members),
            topology=_topology(members), rates=dict(
                episode_quality_eligible=_rate(sum(m["episode_quality_eligible"] is True for m in members), len(members), "all group episodes; independent of mission success"),
                mission_success=_rate(sum(m["mission_success"] is True for m in members), len(members), "all group episodes including unknown"))))
    expected_intents = {sample["intent"] for sample in samples}
    expected_intents.update(attempt["intent"] for candidate in generation.get("candidates", [])
                            for attempt in candidate.get("attempts", []) if isinstance(attempt.get("intent"), str))
    families = set(family_splits)
    families.update(base["family_id"] for base in generation.get("bases", [])
                    if base.get("status") == "accepted" and base.get("family_id"))
    matrix, missing = {}, []
    for family in sorted(families):
        matrix[family] = {}
        for intent in sorted(expected_intents):
            members = [s for s in samples if s["family_id"] == family and s["intent"] == intent]
            qualified = sum(s["episode_quality_eligible"] is True for s in members)
            matrix[family][intent] = dict(episodes=len(members), quality_eligible=qualified,
                mission_success=sum(s["mission_success"] is True for s in members),
                missing_quality_eligible=qualified == 0, run_ids=[s["run_id"] for s in members])
            if not qualified:
                missing.append(dict(family_id=family, intent=intent, reason="no quality-eligible exported episode"))
    leaks = {family: sorted(str(v) for v in splits) for family, splits in family_splits.items() if len(splits) > 1}
    if leaks:
        issues.append("families cross dataset splits")
    common = {name: _summary([v for s in samples for v in s["metrics"][name]]) for name in COMMON_METRICS}
    attempts = [a for item in ledger.get("missions", []) for a in item.get("attempts", [])]
    counts = generation.get("counts", {})
    total = len(samples)
    planning = (_rate(counts["accepted_candidates"], counts["candidates"], "all sampled candidates")
                if "accepted_candidates" in counts and "candidates" in counts else
                dict(numerator=None, denominator=None, fraction=None, denominator_basis="unavailable without generation evidence"))
    return dict(schema_version=2, audit_version=AUDIT_VERSION, dataset_directory=str(root),
        family_scheme=dataset.get("family_scheme"),
        counts=dict(episodes=total, families=len(family_splits), expected_families=len(families), intents=len(expected_intents),
            control_modes=len({s["control_mode"] for s in samples}), base_scenes=counts.get("base_scenes"),
            attempts=len(attempts) if attempt_ledger else None, semantic_unknown=sum(s["mission_success"] is None for s in samples)),
        rates=dict(planning=planning,
            execution_completed=_rate(sum(a.get("run_status") == "completed" for a in attempts), len(attempts), "ledger attempts") if attempt_ledger else
                _rate(sum(s["run_status"] == "completed" for s in samples), total, "exported episodes only; unexported attempts unknown"),
            episode_quality_eligible=_rate(sum(s["episode_quality_eligible"] is True for s in samples), total, "all exported episodes; independent of mission success"),
            semantic_pass=_rate(sum(s["mission_success"] is True for s in samples), total, "all exported episodes including unknown"),
            default_eligible=_rate(sum(s["benchmark_eligible"] is True for s in samples), total, "all exported episodes"),
            strict_eligible=_rate(sum(s["strict_benchmark_eligible"] is True for s in samples), total, "all exported episodes")),
        metrics=common, missing_metrics=[name for name, distribution in common.items() if not distribution["count"]],
        groups=group_reports, id_position_order=_aggregate_order(samples),
        clock_grades=dict(Counter(s["clock_grade"] for s in samples)),
        counterfactual_completeness=dict(qualification="episode_quality_eligible", expected_intents=sorted(expected_intents),
            expectation_source="exported intents plus provided generation attempts/accepted families", matrix=matrix,
            missing=missing, complete=not missing if families and expected_intents else None),
        duplicates=dict(normalized_input_groups={key: count for key, count in input_hashes.items() if count > 1},
            identity_fields_excluded=["task_id", "family_id", "seed", "scene_id"]),
        family_split_leaks=leaks, issues=issues, episodes=samples,
        topology_scope="signature overlap is reported separately per intent/control_mode; no cross-intent signature matching",
        limitation="descriptive audit only; no classifier, accuracy or intention identifiability claim; optional evidence is never recomputed")
