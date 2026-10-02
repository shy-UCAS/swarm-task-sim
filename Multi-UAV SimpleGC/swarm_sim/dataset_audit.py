"""Descriptive mission dataset checks with explicit denominators; no classifier."""

import copy
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .episode_loader import load_episode
from .generation import canonical_hash, checked_path, file_hash
from .protocol import manifest_protocol


def _read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _distribution(values):
    values = sorted(float(v) for v in values if isinstance(v, (int, float))
                    and not isinstance(v, bool) and math.isfinite(v))
    if not values:
        return dict(count=0, min=None, median=None, p95=None, max=None)
    return dict(count=len(values), min=values[0], median=statistics.median(values),
                p95=values[max(0, math.ceil(len(values) * .95) - 1)], max=values[-1])


def _rate(numerator, denominator, basis):
    return dict(numerator=numerator, denominator=denominator,
                fraction=numerator / denominator if denominator else None, denominator_basis=basis)


def _content_hash(task):
    task = copy.deepcopy(task)
    if isinstance(task, dict):
        for name in ("task_id", "family_id", "seed"):
            task.pop(name, None)
        task.get("scenario", {}).pop("scene_id", None)
    return canonical_hash(task)


def audit_dataset(dataset_path, generation_manifest=None, attempt_ledger=None):
    """Audit a frozen export. Unavailable evidence is reported as missing, never zero."""
    root = Path(dataset_path).resolve()
    dataset = _read(root / "dataset_manifest.json")
    if not isinstance(dataset, dict) or not isinstance(dataset.get("episodes"), list):
        raise ValueError("dataset_manifest.json with episodes is required")
    if dataset.get("semantic_protocol", {}).get("task_kind") == "mission_v3":
        from .dataset_audit_v3 import audit_dataset_v3
        return audit_dataset_v3(root, generation_manifest, attempt_ledger)
    entries = dataset["episodes"]
    family_splits, split_families = defaultdict(set), defaultdict(set)
    split_episodes, clocks, vehicle_counts, axes, return_choices = Counter(), Counter(), Counter(), Counter(), Counter()
    protocol_counts, template_counts, input_hashes = Counter(), Counter(), Counter()
    samples, issues, semantic, completed, eligible, strict = [], [], 0, 0, 0, 0
    semantic_known = 0
    metrics = defaultdict(list)
    unique_runs = set()
    for entry in entries:
        if entry["run_id"] in unique_runs:
            raise ValueError("duplicate run ID in dataset audit")
        unique_runs.add(entry["run_id"])
        episode_root = checked_path(root, entry["directory"])
        if file_hash(episode_root / "manifest.json") != entry["analysis_manifest_sha256"]:
            raise ValueError("dataset episode manifest changed")
        episode = load_episode(episode_root)
        manifest = _read(episode_root / "manifest.json", {})
        labels = episode["targets"]
        quality = _read(episode_root / "quality.json", {})
        task = _read(episode_root / "task.json", {}) or {}
        family, split = entry.get("family_id"), entry.get("split")
        split_episodes[split or "unassigned"] += 1
        if family:
            family_splits[family].add(split)
            split_families[split or "unassigned"].add(family)
        protocol = dict(**manifest_protocol(manifest), quality_policy_sha256=manifest.get("quality_policy_sha256"))
        protocol_counts[canonical_hash(protocol)] += 1
        vehicle_counts[str(len(episode["agent_ids"]))] += 1
        is_completed = entry.get("run_status") == "completed"
        completed += is_completed
        success = labels.get("mission_success")
        semantic += success is True
        semantic_known += success is not None
        eligible += entry.get("benchmark_eligible") is True
        strict += entry.get("strict_benchmark_eligible") is True
        clocks[quality.get("clock_quality", {}).get("overall", "unknown")] += 1
        metrics["episode_duration_s"].append(manifest.get("duration_s"))
        metrics["observation_valid_fraction"].extend(quality.get("observation_valid_fraction", {}).values())
        metrics["truth_valid_fraction"].extend(quality.get("truth_valid_fraction", {}).values())
        truth_metric = labels.get("mission_metrics", {}).get("truth", {})
        if not truth_metric:
            truth_metric = _read(episode_root / "semantic_validation.json", {}).get("truth", {})
        coverage = truth_metric.get("coverage", {})
        metrics["global_coverage_ratio"].append(coverage.get("global_coverage_ratio"))
        metrics["repeated_coverage_cell_ratio"].append(coverage.get("repeated_coverage_cell_ratio"))
        constraints = _read(episode_root / "execution_constraints.json", {})
        per_agent = constraints.get("per_agent", {})
        reasons = []
        if success is not True:
            reasons.append("semantic_failed" if success is False else "semantic_unknown")
        for key in ("data_quality_pass", "truth_available_pass", "timing_diagnostic_pass"):
            if quality.get(key) is not True:
                reasons.append(key + ":failed_or_unknown")
        for agent, value in per_agent.items():
            metrics["executed_path_length_m"].append(value.get("truth", {}).get("path_length_m"))
            metrics["airborne_time_s"].append(value.get("armed_to_landed_source_s"))
            for key in ("world_bounds_pass", "path_length_pass", "airborne_time_pass"):
                if value.get(key) is not True:
                    reasons.append(f"{agent}:{key}:failed_or_unknown")
        if quality.get("separation_status") != "clear_observed":
            reasons.append("observation_separation:" + str(quality.get("separation_status", "unknown")))
        if quality.get("truth_separation", {}).get("status") != "clear_observed":
            reasons.append("truth_separation:" + str(quality.get("truth_separation", {}).get("status", "unknown")))
        windows = _read(episode_root / "phase_windows.json", {})
        if isinstance(windows, dict):
            stages = {w.get("phase") for w in windows.get("windows", [])}
            if stages:
                metrics["executed_stage_count"].append(len(stages))
            for window in windows.get("windows", []):
                metrics["barrier_wait_s"].append(window.get("barrier_wait_host_s"))
                metrics["scheduling_wait_s"].append(window.get("scheduling_wait_host_s"))
        if task.get("schema_version") == 2:
            scenario = task["scenario"]
            target = next((r for r in scenario["regions"] if r["id"] == task["mission"]["target_region_id"]), {})
            metrics["region_width_m"].append(target.get("width_m"))
            metrics["region_height_m"].append(target.get("height_m"))
            metrics["speed_m_s"].append(task["execution"]["speed_m_s"])
            axes[task["planner"]["partition_axis"]] += 1
            return_choices[str(task["mission"]["return_required"]).lower()] += 1
            # Coarse bins are only a simple template concentration diagnostic.
            signature = (len(episode["agent_ids"]), task["planner"]["partition_axis"],
                         round(target.get("width_m", 0) / 10), round(target.get("height_m", 0) / 10),
                         task["mission"]["return_required"])
            template_counts[str(signature)] += 1
            spawn_e = [v["east_m"] for v in scenario["vehicles"]]
            spawn_n = [v["north_m"] for v in scenario["vehicles"]]
            metrics["spawn_east_span_m"].append(max(spawn_e) - min(spawn_e))
            metrics["spawn_north_span_m"].append(max(spawn_n) - min(spawn_n))
        input_hashes[_content_hash(task)] += 1
        samples.append(dict(run_id=entry["run_id"], family_id=family, split=split,
            frames=len(episode["t_s"]), agents=len(episode["agent_ids"]), mission_success=success,
            default_eligible=entry.get("benchmark_eligible"), strict_eligible=entry.get("strict_benchmark_eligible"),
            global_coverage_ratio=coverage.get("global_coverage_ratio"),
            per_agent_coverage=coverage.get("per_agent", {}), reasons=reasons))
    leaks = {family: sorted(str(v) for v in splits) for family, splits in family_splits.items() if len(splits) > 1}
    if leaks:
        issues.append("families cross dataset splits")
    if len(protocol_counts) > 1:
        issues.append("mixed label/quality/eligibility protocols")
    generation = _read(Path(generation_manifest), {}) if generation_manifest else {}
    counts = generation.get("counts", {})
    ledger = _read(Path(attempt_ledger), {}) if attempt_ledger else {}
    attempts = [a for item in ledger.get("missions", []) for a in item.get("attempts", [])]
    rates = dict(
        planning=_rate(counts.get("accepted_candidates", 0), counts.get("candidates", 0), "all sampled candidates; unavailable without generation manifest"),
        execution_completed=_rate(sum(a.get("run_status") == "completed" for a in attempts) if attempts else completed,
                                  len(attempts) if attempts else len(entries), "ledger attempts" if attempts else "exported analyzed episodes only"),
        semantic_pass=_rate(semantic, len(entries), "all exported analyzed episodes, including unknown"),
        semantic_pass_known_only=_rate(semantic, semantic_known, "episodes with true/false semantic outcome"),
        default_eligible=_rate(eligible, len(entries), "all exported analyzed episodes"),
        strict_eligible=_rate(strict, len(entries), "all exported analyzed episodes"))
    return dict(schema_version=1, audit_version="mission_dataset_audit_v1", dataset_directory=str(root),
        counts=dict(episodes=len(entries), families=len(family_splits),
                    base_scenes=counts.get("base_scenes"), attempts=len(attempts) if attempt_ledger else len(entries),
                    attempt_count_basis="ledger" if attempt_ledger else "exported episodes only; unexported attempts unknown",
                    semantic_unknown=len(entries) - semantic_known), rates=rates,
        splits={name: dict(episodes=count, families=len(split_families[name])) for name, count in split_episodes.items()},
        metrics={name: _distribution(values) for name, values in metrics.items()},
        diversity=dict(vehicle_counts=dict(vehicle_counts), partition_axes=dict(axes), return_required=dict(return_choices),
                       coarse_template_counts=dict(template_counts),
                       largest_coarse_template_fraction=max(template_counts.values(), default=0) / len(entries) if entries else None),
        clock_grades=dict(clocks), protocols=dict(protocol_counts),
        duplicates=dict(normalized_input_groups={k: v for k, v in input_hashes.items() if v > 1},
                        identity_fields_excluded=["task_id", "family_id", "seed", "scene_id"]),
        family_split_leaks=leaks, issues=issues, episodes=samples,
        missing_metrics=[key for key in ("global_coverage_ratio", "barrier_wait_s", "executed_path_length_m")
                         if not _distribution(metrics[key])["count"]],
        limitation="single mission class; no classification accuracy or claim of intention identifiability; coarse bins do not identify all near-duplicates")
